# Kiến trúc serverless và lựa chọn mức độ quản lý

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích serverless là mô hình vận hành trong đó AWS quản lý phần lớn hạ tầng thực thi và khả năng mở rộng.
- Phân biệt mức độ quản lý giữa dịch vụ serverless, container serverless, container trên EC2, Kubernetes và máy ảo.
- Chọn AWS Lambda, Amazon ECS với AWS Fargate, Amazon ECS Express Mode, Amazon EKS hoặc Amazon EC2 theo thời lượng, runtime, trạng thái, tải và năng lực vận hành.
- Kết hợp API Gateway, Lambda, SQS, SNS, EventBridge và Step Functions để xây dựng kiến trúc đồng bộ, bất đồng bộ và hướng sự kiện.
- Chọn S3, DynamoDB, Aurora Serverless và các dịch vụ dữ liệu theo mô hình truy cập.
- Thiết kế bảo mật, phân quyền IAM, networking, retry, idempotency, concurrency và khả năng phục hồi.
- Đánh giá latency, cold start, throughput, quota, observability và chi phí.
- Dùng AWS SAM, AWS CDK hoặc CloudFormation để triển khai kiến trúc serverless có thể lặp lại.
- Xây dựng tiêu chí lựa chọn mức độ quản lý phù hợp với yêu cầu kỹ thuật và năng lực đội ngũ.

## 1. Serverless giải quyết vấn đề gì?

Trong mô hình truyền thống, đội phát triển hoặc vận hành thường phải chọn máy chủ, cấu hình hệ điều hành, cài runtime, thiết lập autoscaling, theo dõi dung lượng, vá bảo mật và xử lý lỗi phần cứng. Khi lưu lượng tăng, hệ thống cần thêm capacity. Khi lưu lượng giảm, tài nguyên nhàn rỗi vẫn có thể phát sinh chi phí.

Serverless là mô hình trong đó nhà cung cấp cloud quản lý phần lớn hạ tầng thực thi. Đội phát triển tập trung vào mã ứng dụng, dữ liệu, sự kiện, API và chính sách vận hành. Dịch vụ có thể tự cấp phát hoặc thu hồi capacity theo nhu cầu; nhiều dịch vụ tính phí theo request, thời gian thực thi hoặc lượng dữ liệu thực sự sử dụng.

Trên AWS, serverless không chỉ là AWS Lambda. Một ứng dụng serverless thường kết hợp nhiều dịch vụ:

- **Compute:** AWS Lambda hoặc Amazon ECS chạy trên AWS Fargate.
- **API:** Amazon API Gateway, AWS AppSync hoặc Lambda Function URLs.
- **Messaging:** Amazon SQS, Amazon SNS và Amazon EventBridge.
- **Orchestration:** AWS Step Functions hoặc Lambda Durable Functions.
- **Data:** Amazon S3, Amazon DynamoDB, Amazon Aurora Serverless.
- **Identity:** Amazon Cognito, IAM và các cơ chế xác thực API.
- **Observability:** Amazon CloudWatch, AWS X-Ray và các công cụ theo dõi phân tán.
- **Infrastructure as Code:** AWS Serverless Application Model (SAM), AWS CDK, CloudFormation hoặc Terraform.

Ví dụ, khi khách hàng đặt hàng trên website, API Gateway nhận request và gọi Lambda. Lambda ghi đơn hàng vào DynamoDB, gửi message vào SQS, rồi trả mã đơn hàng cho khách. Một worker Lambda đọc queue, xử lý thanh toán hoặc gửi thông báo. Step Functions có thể điều phối quy trình nhiều bước, còn CloudWatch theo dõi lỗi và độ trễ.

Điểm quan trọng là đội phát triển vẫn phải thiết kế kiến trúc, quản lý IAM, dữ liệu, mạng, retry, quan sát và chi phí. Serverless giảm công việc quản lý máy chủ, nhưng không loại bỏ trách nhiệm vận hành ứng dụng.

## 2. Serverless không có nghĩa là không có máy chủ

Serverless có nghĩa là khách hàng không trực tiếp cấp phát, vá lỗi và vận hành máy chủ nền tảng cho phần dịch vụ đó. AWS vẫn chạy workload trên hạ tầng vật lý hoặc môi trường thực thi được quản lý.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Serverless | Nhà cung cấp quản lý hạ tầng thực thi; khách hàng tập trung vào workload và cấu hình dịch vụ |
| Managed service | AWS quản lý một phần hoặc phần lớn vòng đời dịch vụ; mức quản lý tùy dịch vụ |
| Fully managed | Nhà cung cấp chịu trách nhiệm vận hành nhiều thành phần nền tảng, nhưng khách hàng vẫn quản lý dữ liệu, quyền và cấu hình của mình |

Một dịch vụ có thể là managed nhưng không hoàn toàn serverless. Ví dụ, Amazon RDS quản lý database engine và hạ tầng, nhưng khách hàng vẫn chọn instance class, capacity, storage và lịch bảo trì. Amazon Aurora Serverless tự điều chỉnh compute capacity theo nhu cầu và giảm công việc quản lý capacity của database.

Serverless cũng không đồng nghĩa với:

- Không cần thiết kế HA hoặc disaster recovery.
- Không cần giới hạn quyền IAM.
- Không cần theo dõi lỗi và latency.
- Không có giới hạn thời gian chạy, payload, concurrency hoặc throughput.
- Luôn rẻ hơn máy chủ chạy liên tục.
- Không có lock-in vào API và mô hình dữ liệu của dịch vụ.
- Tự động bảo đảm exactly-once cho mọi event.

## 3. Spectrum: từ quản lý ít đến kiểm soát sâu

Có thể hình dung mức độ quản lý như một dải lựa chọn. Ở đầu serverless, AWS quản lý nhiều phần hạ tầng hơn. Ở đầu EC2 tự quản lý, đội vận hành kiểm soát sâu hơn nhưng cũng chịu nhiều trách nhiệm hơn.

~~~mermaid
flowchart LR
    A["Managed serverless services"] --> B["Lambda / managed data / API"]
    B --> C["Serverless containers"]
    C --> D["ECS or EKS on managed capacity"]
    D --> E["Containers on EC2"]
    E --> F["Self-managed compute"]
~~~

| Mức quản lý | AWS services / lựa chọn | Khách hàng chủ yếu quản lý |
|---|---|---|
| Serverless function | AWS Lambda | Code, runtime settings, IAM, event sources, concurrency |
| Serverless application services | API Gateway, SQS, EventBridge, DynamoDB, S3 | API, schema, event contract, access policy, data lifecycle |
| Serverless containers | ECS trên Fargate | Container image, task definition, service, network, scaling policy |
| Container deployment có mặc định tự động | Amazon ECS Express Mode | Image, roles, app config và các tùy chỉnh cần thiết |
| Managed Kubernetes | Amazon EKS | Kubernetes workloads, add-ons, policies; AWS quản lý control plane |
| Kubernetes với compute quản lý sâu hơn | EKS Auto Mode hoặc EKS Fargate | Workloads và Kubernetes configuration; AWS quản lý thêm compute capacity theo mode |
| Container trên EC2 | ECS/EKS với EC2 capacity | Container platform, node lifecycle, OS, patching, scaling |
| Máy ảo | Amazon EC2 | OS, runtime, patching, scaling, capacity, application |

Không phải workload nào cũng cần nằm ở một đầu của spectrum. Một hệ thống có thể dùng Lambda cho API nhỏ, Fargate cho service xử lý liên tục, DynamoDB cho dữ liệu giao dịch và EC2 cho một thành phần legacy cần kernel module riêng.

### 3.1 Mức quản lý và quyền kiểm soát

Mức quản lý càng cao thường giảm công việc bảo trì hạ tầng, nhưng có thể giới hạn runtime, thời gian chạy, quyền truy cập hệ điều hành hoặc cách kiểm soát networking. Mức kiểm soát càng sâu thường tăng tính linh hoạt, đồng thời tăng trách nhiệm vá lỗi, nâng cấp, scaling và giám sát.

Hãy đánh giá mức quản lý theo workload cụ thể, không chỉ theo sở thích công nghệ của đội phát triển.

## 4. Quy trình chọn compute

Trước khi chọn dịch vụ, trả lời các câu hỏi:

1. Workload được gọi theo request, event, schedule, stream hay chạy liên tục?
2. Một lần thực thi kéo dài vài giây, vài phút hay nhiều giờ?
3. Có cần giữ process, WebSocket, session hoặc state trong bộ nhớ không?
4. Có thể đóng gói ứng dụng thành container không?
5. Có cần quyền kiểm soát OS, kernel, GPU, thiết bị hoặc network đặc biệt không?
6. Lưu lượng ổn định hay tăng giảm đột ngột?
7. Độ trễ cold start có ảnh hưởng trải nghiệm không?
8. Workload có thể chạy lại an toàn sau timeout hoặc event duplicate không?
9. Đội ngũ có kinh nghiệm vận hành Kubernetes, container platform hoặc EC2 không?
10. Chi phí nhàn rỗi, chi phí request và chi phí data transfer ảnh hưởng thế nào?

Bảng quyết định nhanh:

| Đặc điểm workload | Lựa chọn nên đánh giá đầu tiên |
|---|---|
| Hàm xử lý ngắn, event-driven, lưu lượng biến động | AWS Lambda |
| API hoặc webhook đơn giản, một function | Lambda Function URL hoặc API Gateway HTTP API |
| API cần API keys, usage plans, private endpoint hoặc WAF integration | API Gateway REST API |
| Container HTTP stateless, muốn triển khai nhanh với mặc định hợp lý | Amazon ECS Express Mode |
| Container chạy liên tục, custom runtime, job dài hoặc cần kiểm soát task resources | Amazon ECS với Fargate |
| Ứng dụng cần Kubernetes API và hệ sinh thái CNCF | Amazon EKS |
| Cần GPU, kernel module, host access hoặc workload đặc thù | EC2 hoặc EKS/ECS trên EC2 |
| Workflow nhiều bước, retry, chờ phê duyệt, cần lịch sử thực thi | AWS Step Functions |
| Workflow bền vững viết theo mô hình function với checkpoint | Lambda Durable Functions |
| File/object event processing | S3 + EventBridge/Lambda/SQS |
| Lưu lượng event lớn cần buffer | SQS hoặc Kinesis tùy mô hình dữ liệu |

Đây là điểm khởi đầu. Cần kiểm tra thêm service quotas, Region availability, network topology, compliance và pricing trước khi quyết định.

## 5. AWS Lambda: compute theo request và event

AWS Lambda chạy code khi nhận invocation từ API, event source hoặc một dịch vụ AWS. AWS quản lý execution environments và tự điều chỉnh số môi trường theo concurrency.

Lambda phù hợp với:

- API backend và microservices có request ngắn.
- Xử lý file khi S3 nhận object mới.
- Event handlers từ EventBridge.
- Worker đọc message từ SQS.
- Xử lý record từ Kinesis hoặc DynamoDB Streams.
- Tác vụ schedule theo EventBridge Scheduler.
- Automation glue code giữa các dịch vụ AWS.

### 5.1 Invocation modes

Có hai kiểu invocation phổ biến:

| Kiểu | Hành vi | Ví dụ |
|---|---|---|
| Synchronous | Caller chờ function hoàn tất và nhận response | API Gateway gọi Lambda |
| Asynchronous | Lambda nhận event vào queue nội bộ và trả xác nhận trước khi xử lý | S3 hoặc EventBridge kích hoạt Lambda |
| Event source mapping | Lambda poll queue/stream, gom batch và gọi function | SQS, Kinesis, DynamoDB Streams |

Synchronous phù hợp khi caller cần kết quả ngay. Asynchronous phù hợp khi có thể xử lý sau và cần tách producer khỏi consumer. Event source mapping phù hợp với queue/stream vì Lambda quản lý polling và batching.

Không nên giả định mọi trigger có cùng retry behavior. Với synchronous invocation, caller hoặc dịch vụ nguồn thường chịu trách nhiệm phản ứng với lỗi. Với asynchronous invocation, Lambda có retry và có thể gửi invocation records đến destination. Với SQS event source mapping, message có thể được nhận lại sau visibility timeout.

### 5.2 Giới hạn thời gian và tài nguyên

Lambda Event Functions có giới hạn thời gian thực thi tối đa 15 phút cho một invocation. Memory có thể cấu hình từ 128 MB đến 10.240 MB; CPU được cấp tỷ lệ theo memory. Các quota concurrency, payload, deployment package và network interface cần được kiểm tra theo Region và tài khoản.

Đây là giới hạn của mô hình Event Function thông thường. Một số Lambda Managed Instances functions có thể chạy tối đa 90 phút cho asynchronous invocation hoặc event source mapping đủ điều kiện, ngoại trừ Amazon MQ và Amazon DocumentDB. Khi workload cần thời lượng dài hơn, kiểm tra rõ compute form factor và kiểu invocation thay vì áp dụng một con số chung cho mọi loại Lambda.

Một invocation vượt giới hạn thời gian cần được chia nhỏ, đưa vào queue, điều phối bằng Step Functions/Durable Functions hoặc chuyển sang compute phù hợp như Fargate.

### 5.3 Cold start và concurrency

Cold start xảy ra khi Lambda cần chuẩn bị execution environment mới. Thời gian khởi tạo phụ thuộc runtime, package size, VPC configuration, initialization code và các dependency.

Các lựa chọn:

- Giảm package size và thời gian khởi tạo.
- Khởi tạo SDK client ngoài handler để tái sử dụng execution environment.
- Dùng Provisioned Concurrency khi cần giảm cold start cho traffic có yêu cầu latency nghiêm ngặt.
- Dùng Reserved Concurrency để giới hạn mức concurrency tối đa và bảo vệ database/downstream.
- Tách function có đặc tính tải khác nhau để quản lý scaling độc lập.

Reserved Concurrency không tính thêm phí nhưng giới hạn capacity dành riêng cho function. Provisioned Concurrency giữ execution environments được khởi tạo sẵn và phát sinh chi phí bổ sung.

### 5.4 Lambda Durable Functions

Lambda Durable Functions hỗ trợ workflow nhiều bước có checkpoint, retry và wait. Một durable execution có thể kéo dài tới một năm, trong khi mỗi lần thực thi code vẫn tuân theo giới hạn invocation của Lambda. Khi execution bị gián đoạn, runtime có thể replay từ checkpoint và bỏ qua các bước đã hoàn thành.

Durable Functions phù hợp với quy trình dài như xử lý đơn hàng, chờ callback, polling dịch vụ ngoài hoặc human-in-the-loop. Nếu cần workflow có state machine hiển thị, service integrations rộng, execution history và điều phối nhiều hệ thống, hãy so sánh với Step Functions.

### 5.5 Lambda MicroVMs và workload có session

Lambda MicroVMs là một compute form factor khác với Lambda Event Functions. MicroVMs cung cấp môi trường cô lập cấp máy ảo, có thể giữ trạng thái trong một session, hỗ trợ Dockerfile-based programming model và thời lượng session dài hơn. Chúng phù hợp với một số môi trường thực thi code cô lập, notebook, sandbox hoặc CI executor.

Không nên đồng nhất MicroVMs với function invocation. Hai mô hình khác nhau về vòng đời, concurrency, billing và cách đóng gói ứng dụng. Hãy kiểm tra availability, quota và giới hạn hiện hành trước khi chọn.

## 6. Serverless containers: Amazon ECS và AWS Fargate

AWS Fargate là compute engine serverless cho container trên Amazon ECS và Amazon EKS. Bạn cung cấp container image, CPU/memory, task definition và các cấu hình cần thiết; AWS quản lý server capacity bên dưới.

Fargate phù hợp khi:

- Ứng dụng cần chạy liên tục.
- Process cần tồn tại lâu hơn 15 phút.
- Cần custom runtime, OS packages hoặc nhiều process trong một container.
- Có batch jobs hoặc worker chạy dài.
- Muốn đóng gói ứng dụng theo container nhưng không quản lý EC2 instances.
- Cần kiểm soát CPU, memory và task networking.

### 6.1 ECS task và service

- **Task definition:** mô tả container image, CPU, memory, environment, port, logging, IAM roles và volume.
- **Task:** một lần chạy của task definition.
- **Service:** duy trì số lượng task mong muốn, thay thế task lỗi và tích hợp load balancer.
- **Cluster:** logical grouping để quản lý ECS services và tasks.

Fargate task có ENI riêng với private IP. Security group gắn với task ENI kiểm soát traffic. Container trong cùng task có thể giao tiếp qua localhost. Task cần route phù hợp để pull image và truy cập AWS services.

### 6.2 ECS Express Mode

Amazon ECS Express Mode đơn giản hóa việc triển khai containerized applications. Để khởi tạo service, bạn cung cấp container image, task execution role và infrastructure role. Express Mode tự cấu hình Fargate-based ECS service, URL, load balancer với TLS, autoscaling, monitoring và networking.

Express Mode phù hợp với web applications và APIs stateless cần HTTPS public/private, rapid prototyping hoặc mô hình self-service cho developer teams. Các tài nguyên được tạo vẫn hiển thị và có thể quản lý trực tiếp trong tài khoản AWS.

Không có phụ phí riêng cho Express Mode; khách hàng thanh toán các tài nguyên nền như Fargate, load balancer, CloudWatch và data transfer.

### 6.3 AWS App Runner: lưu ý về khả năng tiếp nhận khách hàng

AWS App Runner đã ngừng tiếp nhận khách hàng mới từ ngày 30/04/2026. Khách hàng hiện hữu vẫn có thể tiếp tục sử dụng dịch vụ và tạo tài nguyên mới. Nếu đang thiết kế cho khách hàng mới cần trải nghiệm triển khai container đơn giản, hãy đánh giá Amazon ECS Express Mode.

Đây là thay đổi về availability có thể ảnh hưởng trực tiếp đến lựa chọn dịch vụ. Không nên lấy các tutorial App Runner cũ làm mặc định cho kiến trúc mới.

## 7. Amazon EKS, EC2 và lựa chọn Kubernetes

Amazon EKS cung cấp Kubernetes control plane được AWS quản lý. Đội vận hành vẫn cần hiểu Kubernetes API, deployment, service, ingress, resource requests/limits, network policy và observability.

Chọn EKS khi:

- Kubernetes là nền tảng chuẩn của tổ chức.
- Ứng dụng phụ thuộc CRDs, operators hoặc CNCF ecosystem.
- Cần portability giữa môi trường.
- Có platform engineering team đủ năng lực vận hành cluster và developer platform.
- Workload cần orchestration của Kubernetes.

EKS Fargate cho phép chạy pod trên serverless compute mà không quản lý worker nodes cho các pod phù hợp. EKS Auto Mode tự động hóa thêm compute, storage và networking infrastructure theo khả năng của mode. Cần kiểm tra compatibility, DaemonSet requirements, privileged workloads, storage và scheduling constraints.

### 7.1 Khi nào dùng EC2?

EC2 phù hợp khi cần:

- Quyền kiểm soát hệ điều hành hoặc kernel.
- GPU/accelerator hoặc phần cứng đặc thù.
- Agent, daemon hoặc driver không tương thích với serverless compute.
- Workload chạy liên tục, utilization ổn định và có thể tối ưu capacity.
- Legacy software yêu cầu môi trường máy chủ riêng.
- Cấu hình mạng, storage hoặc host-level tuning đặc biệt.

EC2 có thể được quản lý bằng Auto Scaling Groups, Launch Templates, Systems Manager và Image Builder. Mức kiểm soát cao đi cùng trách nhiệm patch, hardening, monitoring và capacity planning.

### 7.2 So sánh ECS/Fargate, EKS và EC2

| Tiêu chí | Lambda | ECS + Fargate | EKS | EC2 |
|---|---|---|---|---|
| Đơn vị triển khai | Function | Container task/service | Kubernetes pod/workload | VM hoặc container host |
| Process liên tục | Không phù hợp với Event Function | Có | Có | Có |
| Thời gian một lần chạy | Tối đa 15 phút với Event Function | Có thể chạy dài | Có thể chạy dài | Theo thiết kế |
| Quản lý OS/host | AWS | AWS quản lý host | Tùy Fargate/Auto Mode/EC2 | Khách hàng |
| Kubernetes API | Không | Không bắt buộc | Có | Có thể tự cài |
| Scale-to-zero | Có thể với event-driven invocation | Service có thể cấu hình desired count 0 | Tùy workload/autoscaler | Cần cấu hình |
| Quyền kiểm soát hạ tầng | Thấp | Trung bình | Cao ở lớp Kubernetes | Cao |
| Công việc vận hành | Thấp hơn | Trung bình | Cao hơn nếu tự quản trị cluster | Cao |

## 8. Chọn lớp API

API layer là cổng giao tiếp giữa client và backend. Lựa chọn phụ thuộc giao thức, xác thực, traffic control, private networking và khả năng quản lý API.

| Lựa chọn | Phù hợp |
|---|---|
| API Gateway HTTP API | HTTP API nhẹ, chi phí thấp hơn, tích hợp Lambda hoặc HTTP backend |
| API Gateway REST API | API management phong phú: API keys, usage plans, request validation, per-client throttling, WAF integration và private endpoints |
| API Gateway WebSocket API | Kết nối hai chiều lâu dài cho chat, dashboard realtime hoặc game |
| Lambda Function URL | Endpoint HTTPS trực tiếp cho một Lambda khi không cần đầy đủ tính năng API Gateway |
| AWS AppSync | GraphQL API, subscriptions và tích hợp data sources |
| Application Load Balancer | HTTP routing đến ECS/EKS/EC2 và có thể tích hợp Lambda target |

HTTP API và REST API không giống nhau về feature set. Chọn HTTP API khi yêu cầu gọn và không cần các tính năng quản trị chuyên sâu. Chọn REST API khi cần các tính năng như API keys, usage plans, request validation, WAF integration hoặc private API endpoint.

Function URL đơn giản và phù hợp webhook hoặc endpoint cho một function. Khi cần quota/throttling theo client, API lifecycle, caching hoặc nhiều route, API Gateway thường phù hợp hơn.

## 9. Messaging và event-driven architecture

Event-driven architecture (EDA) giúp producer phát sự kiện mà không cần biết tất cả consumer. Các thành phần có thể triển khai và scale độc lập.

| Dịch vụ | Mô hình | Dùng khi |
|---|---|---|
| Amazon SQS | Queue | Buffer, load leveling, xử lý bất đồng bộ |
| Amazon SNS | Pub/sub fan-out | Một sự kiện cần gửi đến nhiều subscriber |
| Amazon EventBridge | Event bus và content-based routing | Route event từ AWS services, SaaS hoặc custom applications |
| Amazon Kinesis Data Streams | Event stream | Ingest và xử lý dữ liệu liên tục, thứ tự theo shard |
| Amazon MSK | Managed Kafka | Workload cần Kafka ecosystem hoặc protocol compatibility |

### 9.1 Queue với SQS

Queue tách producer khỏi consumer. Khi consumer chậm, message nằm trong queue thay vì làm request của producer kéo dài. SQS Standard cung cấp at-least-once delivery và best-effort ordering. SQS FIFO hỗ trợ thứ tự theo message group và cơ chế exactly-once processing theo phạm vi tính năng FIFO.

Với SQS + Lambda:

- Lambda poll queue và gửi một batch message cho function.
- Message được ẩn trong visibility timeout khi đang xử lý.
- Nếu function xử lý thành công batch, Lambda xóa message.
- Nếu batch lỗi, các message có thể xuất hiện lại sau visibility timeout.
- Cần idempotency vì message có thể được xử lý lặp.
- Dùng partial batch response để chỉ trả lại những message lỗi.
- Dùng dead-letter queue (DLQ) để cô lập message không thể xử lý.

AWS khuyến nghị visibility timeout của queue ít nhất bằng sáu lần function timeout. Nếu dùng batching window, cần cộng thêm thời gian đó theo hướng dẫn hiện hành. Cấu hình redrive policy và maxReceiveCount theo khả năng phục hồi của ứng dụng.

### 9.2 Fan-out với SNS

SNS phù hợp khi một event cần nhiều consumer độc lập. Ví dụ, sau khi đơn hàng được tạo, SNS có thể fan-out tới:

- Queue xử lý thanh toán.
- Queue gửi email.
- Queue cập nhật analytics.
- Queue đồng bộ hệ thống CRM.

Mỗi subscriber có thể xử lý độc lập. Dùng subscription filter policy để chỉ gửi message phù hợp đến từng subscriber.

### 9.3 Event routing với EventBridge

EventBridge phù hợp với event bus cần định tuyến theo nội dung. Producer gửi event vào bus; rules lọc event theo source, detail-type hoặc trường trong payload rồi chuyển đến target như Lambda, Step Functions, SQS hoặc SNS.

EventBridge hữu ích khi cần tích hợp AWS services, SaaS partners và custom applications. Định nghĩa event contract rõ ràng để consumer không phụ thuộc vào chi tiết nội bộ của producer.

### 9.4 Khi nào dùng stream?

Kinesis Data Streams phù hợp với dữ liệu liên tục có tốc độ cao, yêu cầu xử lý theo thứ tự trong partition key hoặc nhiều consumer đọc cùng stream. SQS phù hợp hơn với task queue và công việc độc lập. EventBridge phù hợp với routing event nghiệp vụ. Không dùng một dịch vụ cho mọi loại message.

## 10. Orchestration: Step Functions và Lambda Durable Functions

Một workflow nghiệp vụ thường gồm nhiều bước: kiểm tra đơn hàng, giữ tồn kho, thanh toán, giao hàng và thông báo. Nếu một Lambda gọi tiếp nhiều Lambda khác theo chuỗi, code điều phối có thể trở nên khó đọc, khó retry và khó phục hồi.

AWS Step Functions biểu diễn workflow bằng state machine. Mỗi state có thể gọi Lambda, tích hợp trực tiếp dịch vụ AWS, rẽ nhánh, chạy song song, retry, catch lỗi hoặc chờ callback.

### 10.1 Standard Workflow

Standard Workflow phù hợp với quy trình dài, cần lịch sử thực thi và khả năng audit. Một execution có thể kéo dài tối đa một năm. Mô hình thực thi mặc định exactly-once ở cấp workflow state; nếu cấu hình Retry, task có thể chạy lại theo chính sách đó.

Dùng Standard cho:

- Quy trình đơn hàng hoặc thanh toán.
- Human approval.
- Saga nhiều dịch vụ.
- ETL nhiều bước.
- Workflow cần execution history chi tiết.

### 10.2 Express Workflow

Express Workflow phù hợp với xử lý event khối lượng lớn và thời gian ngắn, tối đa năm phút. Asynchronous Express dùng at-least-once; Synchronous Express dùng at-most-once. Vì có thể xử lý lặp trong một số trường hợp, các bước cần idempotent.

Express không hỗ trợ một số service integration patterns như .sync và .waitForTaskToken. Kiểm tra yêu cầu callback, lịch sử và execution semantics trước khi chọn.

### 10.3 Lambda Durable Functions

Durable Functions cung cấp checkpoint, retry và wait trong mô hình lập trình Lambda. Có thể dùng khi muốn viết logic nhiều bước bằng code và để runtime duy trì tiến độ qua các lần invocation. Mỗi lần invocation vẫn có giới hạn riêng; durable execution quản lý tiến trình dài hơn.

### 10.4 So sánh

| Tiêu chí | Step Functions Standard | Step Functions Express | Lambda Durable Functions |
|---|---|---|---|
| Mục tiêu | Workflow dài, audit rõ | Event volume lớn, ngắn | Durable multi-step logic trong Lambda |
| Thời lượng | Tối đa 1 năm | Tối đa 5 phút | Durable execution có thể tới 1 năm |
| Semantics | Exactly-once mặc định, có thể retry | Async at-least-once; sync at-most-once | Checkpoint/replay theo durable operations |
| Quan sát | Execution history chi tiết | CloudWatch Logs và console | Durable execution state/observability |
| Phù hợp | Saga, approval, business workflow | Ingestion, transformation, high-volume events | Quy trình dài cần checkpoint nhưng muốn code-first |

Không nên chọn workflow type chỉ dựa trên giá. Hãy xét semantics, thời lượng, audit, callback, retry và khả năng idempotent của từng bước.

## 11. Lớp dữ liệu trong kiến trúc serverless

Compute serverless cần data services có mô hình vận hành phù hợp. Dữ liệu vẫn là phần cần thiết kế kỹ nhất: consistency, transaction, partition key, indexing, backup, retention và quyền truy cập.

| Dịch vụ | Mô hình dữ liệu | Phù hợp |
|---|---|---|
| Amazon S3 | Object storage | File, ảnh, video, static assets, data lake |
| Amazon DynamoDB | Key-value/document NoSQL | Access pattern rõ, throughput lớn, latency thấp |
| Amazon Aurora Serverless | Relational SQL | Join, transaction và SQL compatibility với capacity tự điều chỉnh |
| Amazon RDS | Managed relational database | Workload cần engine/instance model truyền thống |
| Amazon ElastiCache | In-memory cache | Giảm latency và tải database |
| Amazon EFS | Shared file system | Container/function cần shared POSIX file storage theo thiết kế phù hợp |

### 11.1 DynamoDB

DynamoDB phù hợp khi access patterns có thể xác định từ đầu và dữ liệu có thể thiết kế theo partition key/sort key. Không cần quản lý database server hoặc connection pool như database relational.

Thiết kế cần chú ý:

- Partition key có phân bố đều để tránh hot partition.
- GSI/LSI theo access patterns thực tế.
- Conditional writes hoặc transactions khi cần kiểm soát cập nhật.
- TTL cho dữ liệu có vòng đời.
- On-demand hoặc provisioned capacity theo traffic profile.
- Backup, point-in-time recovery và global tables nếu yêu cầu DR/multi-Region.

### 11.2 Aurora Serverless

Aurora Serverless phù hợp với relational workloads cần SQL và transaction, nhưng muốn capacity điều chỉnh theo nhu cầu. Không nên chọn chỉ vì tên có chữ Serverless. Cần đánh giá minimum/maximum ACUs, scaling behavior, connection count, failover, RDS Proxy và chi phí khi database duy trì capacity tối thiểu.

### 11.3 S3 và event processing

S3 thường là điểm vào của pipeline xử lý file. Khi object được tạo, S3 có thể gửi event tới Lambda, SQS hoặc EventBridge tùy kiến trúc. Với file lớn hoặc xử lý dài, nên đưa event vào queue để buffer và tránh xử lý trực tiếp trong request upload.

## 12. Các kiến trúc serverless tham khảo

### 12.1 API đồng bộ

~~~mermaid
flowchart LR
    C["Web / Mobile client"] --> A["API Gateway HTTP API"]
    A --> L["Lambda"]
    L --> D["DynamoDB"]
    L --> R["API response"]
    R --> C
~~~

Dùng khi client cần response ngay. Giữ request path ngắn. Nếu nghiệp vụ kéo dài, trả 202 Accepted cùng job ID rồi xử lý bất đồng bộ.

### 12.2 Xử lý đơn hàng bất đồng bộ

~~~mermaid
flowchart TD
    C["Client"] --> A["API Gateway"]
    A --> L["Order API Lambda"]
    L --> D["DynamoDB: order state"]
    L --> Q["SQS: order queue"]
    Q --> W["Worker Lambda"]
    W --> S["Step Functions"]
    S --> P["Payment"]
    S --> I["Inventory"]
    S --> N["Notification"]
    S --> D
    Q -. "Repeated failures" .-> DLQ["Dead-letter queue"]
~~~

API xác nhận đã nhận đơn hàng sau khi lưu trạng thái và enqueue message. Worker xử lý payment/inventory và cập nhật order status. Queue hấp thụ traffic burst; Step Functions điều phối các bước có retry và compensation.

### 12.3 Pipeline xử lý file

~~~mermaid
flowchart LR
    U["User uploads"] --> S3["Amazon S3"]
    S3 --> EB["EventBridge / SQS"]
    EB --> L["Lambda metadata validator"]
    L --> Q["SQS processing queue"]
    Q --> F["Fargate or Lambda worker"]
    F --> O["S3 output"]
    F --> M["DynamoDB job metadata"]
~~~

Dùng Lambda cho bước validation ngắn. Dùng Fargate khi file cần xử lý lâu, dependency native lớn hoặc cần CPU/memory ổn định. Queue giúp điều tiết tốc độ xử lý.

### 12.4 Web application chạy container

~~~mermaid
flowchart TD
    U["Browser / Mobile"] --> ALB["Application Load Balancer"]
    ALB --> ECS["ECS Express Mode / ECS service"]
    ECS --> F["AWS Fargate tasks"]
    F --> DB["Aurora Serverless or DynamoDB"]
    F --> Q["SQS / EventBridge"]
    Q --> W["Lambda / Fargate workers"]
    ECS --> CW["CloudWatch"]
    W --> CW
~~~

Dùng container khi ứng dụng cần server process liên tục, framework hiện có hoặc runtime tùy chỉnh. ECS Express Mode giảm phần cấu hình ban đầu; ECS service/Fargate cho phép kiểm soát task, network, load balancer và scaling chi tiết hơn.

## 13. Đồng bộ hay bất đồng bộ?

Chọn kiểu giao tiếp dựa trên trải nghiệm client, khả năng chịu lỗi và mức độ phụ thuộc giữa các thành phần.

| Tiêu chí | Synchronous | Asynchronous |
|---|---|---|
| Client cần kết quả ngay | Có | Thường không |
| Producer phụ thuộc consumer | Cao hơn | Thấp hơn |
| Buffer khi consumer chậm | Hạn chế | Có thể dùng queue |
| Retry | Caller hoặc service nguồn xử lý | Queue/workflow/service xử lý |
| Latency user-facing | Bao gồm toàn bộ downstream trong request path | Có thể trả ACK sớm |
| Phù hợp | Read API, validation ngắn | Email, image processing, order fulfillment |

Không nên kéo dài API request để chờ nhiều hệ thống downstream. Với tác vụ dài, trả job ID và cung cấp endpoint truy vấn trạng thái hoặc push notification.

## 14. Idempotency, retry và xử lý lỗi

Trong kiến trúc phân tán, event có thể được gửi lại do timeout, network error hoặc retry. Lambda event source mappings xử lý at-least-once; một message có thể được xử lý nhiều lần.

Idempotency bảo đảm xử lý lặp không tạo thêm side effect ngoài ý muốn.

Ví dụ, khi nhận yêu cầu tạo đơn hàng, dùng orderId hoặc idempotency key làm khóa nghiệp vụ. Ghi nhận key trong DynamoDB bằng conditional write. Nếu cùng key được gửi lại, trả kết quả đã lưu thay vì trừ tồn kho hoặc charge payment lần nữa.

Các nguyên tắc:

- Dùng idempotency key cho API có side effect.
- Ghi trạng thái xử lý trước/sau side effect theo transaction design.
- Chọn retry có exponential backoff và jitter.
- Phân biệt lỗi tạm thời với lỗi dữ liệu không thể phục hồi.
- Dùng DLQ để cô lập poison messages.
- Thiết kế redrive process và công cụ replay có kiểm soát.
- Ghi correlation ID và business ID vào logs.

### 14.1 SQS với partial batch response

Khi một batch có nhiều message và chỉ một message lỗi, mặc định cả batch có thể được trả lại queue. Bật ReportBatchItemFailures để function báo các message lỗi, giúp tránh xử lý lại các message đã thành công.

Visibility timeout phải đủ dài để Lambda xử lý batch và retry. AWS khuyến nghị ít nhất sáu lần function timeout; nếu có batching window, cộng thêm window theo hướng dẫn SQS event source mapping.

### 14.2 Retry không phải lúc nào cũng tốt

Retry có thể làm tăng tải lên downstream đang lỗi. Khi database quá tải, retry dồn dập có thể làm tình trạng tệ hơn. Dùng backoff, giới hạn concurrency, queue buffer, circuit breaker ở lớp ứng dụng và DLQ để kiểm soát.

## 15. Bảo mật trong kiến trúc serverless

Serverless không loại bỏ trách nhiệm bảo mật. Mỗi function, task, state machine và event source cần quyền đúng phạm vi.

### 15.1 IAM least privilege

- Mỗi Lambda function có execution role riêng theo nghiệp vụ.
- ECS task execution role dùng cho image pull, logs và secret injection; task role dùng cho quyền của ứng dụng.
- Step Functions execution role chỉ cho phép gọi các service integrations cần thiết.
- Giới hạn iam:PassRole vào đúng role và dịch vụ.
- Dùng resource-level permissions khi API hỗ trợ.
- Tránh chia sẻ một role AdministratorAccess cho toàn bộ workload.

### 15.2 API authorization

API Gateway có thể tích hợp IAM authorization, JWT authorizers, Cognito hoặc Lambda authorizers tùy API type. Không coi API key là cơ chế xác thực người dùng; API keys chủ yếu phục vụ usage plans và nhận diện client theo mục đích quản lý traffic.

Dùng TLS cho public APIs, xác thực đầu vào, validate payload, giới hạn kích thước request và cấu hình throttling. Với private APIs, thiết kế VPC endpoints, resource policies và DNS resolution phù hợp.

### 15.3 Secrets và dữ liệu nhạy cảm

Không hard-code secret trong source code, container image hoặc event payload. Dùng AWS Secrets Manager hoặc Systems Manager Parameter Store. Dùng KMS encryption và giới hạn quyền đọc secret theo execution role.

Không ghi access token, password, payment data hoặc PII vào logs. Xác định retention, redaction và quyền truy cập log ngay từ đầu.

### 15.4 VPC networking

Lambda mặc định chạy trong môi trường do AWS quản lý và có thể truy cập Internet. Khi gắn Lambda vào VPC của tài khoản, function dùng networking của VPC để truy cập private resources. Nếu cần truy cập Internet, VPC phải có NAT hoặc đường egress phù hợp. Gắn Lambda vào public subnet không tự cấp Internet access.

Fargate task có ENI riêng. Cần security groups, subnet, route, DNS, NAT hoặc VPC endpoints cho các dịch vụ mà task cần truy cập. Dùng private subnets và VPC endpoints khi phù hợp để giảm phụ thuộc Internet.

## 16. Reliability và khả năng phục hồi

Một kiến trúc serverless cần xem xét lỗi ở từng dịch vụ và từng boundary.

### 16.1 Failure isolation

- Dùng queue để tách producer khỏi consumer.
- Dùng timeout rõ ràng cho downstream calls.
- Giới hạn concurrency để bảo vệ database.
- Tách critical path khỏi analytics hoặc notification path.
- Dùng retry và DLQ có kiểm soát.
- Tránh một function làm quá nhiều nghiệp vụ không liên quan.

### 16.2 Multi-AZ và multi-Region

Nhiều dịch vụ serverless được AWS quản lý với tính sẵn sàng cao trong Region. Tuy nhiên, multi-AZ service availability không đồng nghĩa ứng dụng tự động có multi-Region DR.

Thiết kế DR cần xác định:

- RTO: thời gian tối đa chấp nhận để khôi phục dịch vụ.
- RPO: lượng dữ liệu tối đa chấp nhận mất.
- Data replication strategy.
- DNS/API failover.
- Deployment pipeline ở Region dự phòng.
- IAM, secrets, KMS keys và network dependencies.
- Runbook và bài diễn tập failover/failback.

DynamoDB Global Tables, S3 replication, Aurora Global Database hoặc backup/restore là các lựa chọn khác nhau. Chọn theo RPO/RTO, consistency, chi phí và cách ứng dụng xử lý conflict.

### 16.3 Dependency management

Nếu API Lambda phụ thuộc một relational database, burst traffic có thể tạo quá nhiều database connections. Dùng RDS Proxy, giới hạn concurrency và cache khi phù hợp. Nếu consumer chậm, SQS giúp buffer thay vì để request path tạo áp lực lên database.

## 17. Performance và latency

Serverless có thể scale nhanh nhưng latency phụ thuộc toàn bộ request path.

Các yếu tố:

- Cold start của Lambda.
- Runtime initialization và package size.
- API Gateway overhead.
- Số hop giữa services.
- Database latency và connection management.
- VPC networking và NAT path.
- Serialization, payload size và batch size.
- Throttling hoặc concurrency limit.
- Provisioned capacity ở data layer.

Các cách cải thiện:

- Giảm số lần gọi service không cần thiết.
- Reuse SDK clients và connections trong Lambda execution environment.
- Chọn memory phù hợp để có CPU cần thiết.
- Dùng Provisioned Concurrency khi latency SLO yêu cầu.
- Dùng cache hoặc DynamoDB access patterns phù hợp.
- Batch event khi throughput cao.
- Đặt service cùng Region và hạn chế cross-Region calls.
- Dùng response streaming khi cần progressive response và service hỗ trợ.

Không tối ưu cold start trước khi đo. Với workload bất đồng bộ chạy nền, cold start có thể không ảnh hưởng business outcome đáng kể.

## 18. Observability cho ứng dụng serverless

Một request có thể đi qua API Gateway, Lambda, DynamoDB, SQS, worker Lambda và Step Functions. Nếu chỉ xem log của một function, sẽ khó hiểu toàn bộ business transaction.

Cần có:

- Structured logs với timestamp, severity, service, function, request ID và correlation ID.
- Metrics cho request count, error rate, duration, throttles, queue age/depth và downstream latency.
- Distributed tracing để theo dõi request qua nhiều dịch vụ.
- Dashboards và alarms theo SLO.
- Business metrics như order success rate hoặc payment failure rate.
- Log retention và quyền truy cập theo phân loại dữ liệu.

Amazon CloudWatch cung cấp logs, metrics, alarms và dashboards. AWS X-Ray hoặc OpenTelemetry có thể giúp trace request qua các thành phần hỗ trợ. AWS Lambda Powertools hỗ trợ logging, tracing, metrics và idempotency theo runtime.

Đặt correlation ID từ API boundary và truyền qua event payload/headers. Khi event đi qua queue, ghi nhận message ID và business ID để có thể truy vết.

## 19. Deployment và Infrastructure as Code

Serverless application thường gồm nhiều tài nguyên AWS. Tạo từng resource thủ công dễ gây drift giữa dev, test và production.

| Công cụ | Phù hợp |
|---|---|
| AWS SAM | Ứng dụng Lambda/API Gateway/DynamoDB/Step Functions theo mô hình serverless |
| AWS CDK | Hạ tầng phức tạp, construct tái sử dụng và logic bằng ngôn ngữ lập trình |
| CloudFormation | Native IaC và quản lý stack |
| Terraform | Quản trị hạ tầng đa cloud hoặc tổ chức đã chuẩn hóa HCL |

Pipeline nên có các bước:

1. Unit test và contract test.
2. Static analysis và dependency scanning.
3. Build artifact/container image.
4. Kiểm tra IaC và policy.
5. Deploy vào môi trường test.
6. Integration test và smoke test.
7. Canary hoặc linear deployment.
8. Theo dõi alarm sau deploy.
9. Rollback nếu error rate hoặc latency vượt ngưỡng.

Với Lambda, dùng version và alias để tách $LATEST khỏi production traffic. Với ECS service, dùng deployment circuit breaker, health checks và chiến lược rolling/canary phù hợp. Với Step Functions, version hóa state machine definition và kiểm tra tương thích event contract.

## 20. Chi phí: serverless có luôn rẻ hơn không?

Không. Serverless giảm chi phí capacity nhàn rỗi trong nhiều workload, nhưng tổng chi phí còn gồm request, duration, memory, API calls, message operations, data transfer, logs, tracing và database capacity.

| Thành phần | Đơn vị chi phí thường gặp |
|---|---|
| Lambda | Số request và GB-second |
| API Gateway | Số API calls, data transfer và feature liên quan |
| SQS/SNS/EventBridge | API operations, event volume và payload |
| Step Functions | State transitions hoặc executions/duration/memory theo workflow type |
| Fargate | vCPU, memory, ephemeral storage và thời gian task chạy |
| DynamoDB | Read/write request units hoặc on-demand request, storage và backup |
| Aurora Serverless | ACU capacity, storage, I/O và backup theo cấu hình |
| CloudWatch | Log ingestion/storage, metrics và queries |
| NAT Gateway | Giờ hoạt động và data processing |
| Data transfer | Data transfer theo hướng, Region và destination |

Một service Fargate chạy liên tục 24/7 có thể có chi phí gần với capacity provisioned, dù không quản lý host. Một Lambda function chạy vài millisecond với traffic thấp có thể rẻ hơn. Ngược lại, workload CPU-heavy liên tục có thể phù hợp hơn với container hoặc EC2 được right-size.

Cách đánh giá:

1. Ước lượng request/event volume.
2. Đo duration và memory/CPU.
3. Tính concurrency và burst.
4. Ước lượng queue operations và workflow steps.
5. Tính database capacity và connection overhead.
6. Tính logs, traces và retention.
7. Tính data transfer, NAT và cross-AZ/Region.
8. So sánh theo traffic thấp, trung bình và peak.
9. Đưa chi phí vận hành và nhân lực vào quyết định.

## 21. Rủi ro và giới hạn của kiến trúc serverless

| Rủi ro | Tác động | Cách giảm thiểu |
|---|---|---|
| Vendor lock-in | Phụ thuộc event schema và managed APIs | Dùng contract rõ, adapter layer và IaC |
| Distributed debugging | Khó theo dõi request qua nhiều dịch vụ | Correlation ID, structured logs và tracing |
| Duplicate events | Side effect lặp | Idempotency key và conditional writes |
| Retry storm | Downstream quá tải | Backoff, concurrency limits, queue và DLQ |
| Cold start | Tăng latency | Provisioned Concurrency hoặc giảm init |
| Quota exhaustion | Throttling hoặc deploy failure | Theo dõi quota, đặt alarm và request increase |
| Database connection surge | Database cạn connection | RDS Proxy, pooling và reserved concurrency |
| Event schema drift | Consumer lỗi khi producer đổi payload | Versioned schema và backward compatibility |
| Observability cost | Log/trace volume tăng | Sampling, retention và filtering |
| Cost surprise | Burst hoặc loop tạo request lớn | Budgets, alarms, reserved concurrency và kill switch |

Một event-driven system cần thiết kế khả năng replay. Replay phải có giới hạn, idempotency và khả năng kiểm tra dữ liệu đầu vào. Không nên phát lại toàn bộ queue production nếu chưa hiểu side effects.

## 22. Case study: kiến trúc đặt hàng cho cửa hàng trực tuyến

Một cửa hàng cần tiếp nhận đơn hàng, cập nhật tồn kho, thanh toán và gửi email xác nhận. Traffic tăng mạnh trong các đợt khuyến mãi. Khách hàng cần nhận phản hồi nhanh rằng đơn hàng đã được tiếp nhận.

### Yêu cầu

- API phản hồi trong vài trăm millisecond ở điều kiện bình thường.
- Có thể tiếp nhận burst traffic.
- Không tạo hai đơn hàng khi client retry request.
- Thanh toán và email có thể xử lý bất đồng bộ.
- Lỗi thanh toán cần retry và có quy trình điều tra.
- Đội vận hành xem được trạng thái từng đơn hàng.

### Thiết kế

1. API Gateway HTTP API nhận request.
2. Lambda kiểm tra payload và idempotency key.
3. Lambda ghi order record vào DynamoDB bằng conditional write.
4. Lambda gửi order event vào SQS.
5. Worker Lambda đọc queue và gọi Step Functions Standard.
6. Step Functions kiểm tra tồn kho, gọi payment service, cập nhật order state và phát event.
7. SNS/EventBridge phân phối event sang email và analytics consumers.
8. DLQ giữ message không thể xử lý sau retry.
9. CloudWatch và X-Ray theo dõi latency, lỗi và correlation ID.

### Vì sao không xử lý toàn bộ trong một Lambda?

Nếu giữ request mở cho đến khi thanh toán, inventory và email hoàn tất, API sẽ phụ thuộc latency và availability của tất cả downstream services. Queue và workflow giúp tách tiếp nhận đơn hàng khỏi các bước có thể kéo dài.

### Khi nào dùng Fargate?

Nếu một bước xử lý yêu cầu binary/native dependencies lớn, CPU liên tục hoặc thời gian chạy dài, có thể chuyển worker đó sang ECS/Fargate và giữ các bước event-driven ngắn trên Lambda.

## 23. Lab: triển khai API nhận đơn hàng và xử lý qua SQS

Lab minh họa kiến trúc tối giản với API Gateway HTTP API, Lambda, DynamoDB, SQS và DLQ. Dùng tài khoản sandbox và Region thử nghiệm. Các giá trị tên tài nguyên có thể thay đổi theo môi trường.

### Bước 1: chuẩn bị AWS SAM

Cài AWS SAM CLI, AWS CLI và cấu hình credentials cho tài khoản lab. Tạo thư mục:

~~~bash
mkdir serverless-order-lab
cd serverless-order-lab
~~~

### Bước 2: tạo template

Tạo file template.yaml:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Minimal serverless order intake and worker

Globals:
  Function:
    Runtime: python3.12
    Timeout: 20
    MemorySize: 256
    Tracing: Active

Resources:
  OrdersTable:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: orderId
          AttributeType: S
      KeySchema:
        - AttributeName: orderId
          KeyType: HASH
      SSESpecification:
        SSEEnabled: true

  OrdersDeadLetterQueue:
    Type: AWS::SQS::Queue

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 130
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDeadLetterQueue.Arn
        maxReceiveCount: 5

  OrderApiFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: app.create_order
      Environment:
        Variables:
          ORDERS_TABLE: !Ref OrdersTable
          ORDERS_QUEUE_URL: !Ref OrdersQueue
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref OrdersTable
        - SQSSendMessagePolicy:
            QueueName: !GetAtt OrdersQueue.QueueName
      Events:
        CreateOrder:
          Type: HttpApi
          Properties:
            Path: /orders
            Method: POST

  OrderWorkerFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: app.process_order
      Environment:
        Variables:
          ORDERS_TABLE: !Ref OrdersTable
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref OrdersTable
      Events:
        OrdersQueueEvent:
          Type: SQS
          Properties:
            Queue: !GetAtt OrdersQueue.Arn
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 5
            FunctionResponseTypes:
              - ReportBatchItemFailures

Outputs:
  OrdersApiId:
    Description: HTTP API ID; construct the URL with the API ID and Region
    Value: !Ref ServerlessHttpApi
  OrdersTableName:
    Value: !Ref OrdersTable
  OrdersQueueUrl:
    Value: !Ref OrdersQueue
~~~

Queue visibility timeout là 130 giây, lớn hơn sáu lần function timeout 20 giây cộng batching window 5 giây. Khi thay timeout hoặc batching window, hãy tính lại theo khuyến nghị của AWS. API URL có dạng HTTPS với API ID, Region và execute-api domain; dùng output API ID để ghép URL theo Region triển khai.

### Bước 3: tạo handler mẫu

Tạo file src/app.py:

~~~python
import json
import os
import uuid
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")
orders = dynamodb.Table(os.environ["ORDERS_TABLE"])
queue_url = os.environ["ORDERS_QUEUE_URL"]


def create_order(event, context):
    body = json.loads(event.get("body") or "{}")
    order_id = body.get("orderId") or str(uuid.uuid4())
    amount = body.get("amount")

    if amount is None or amount <= 0:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "amount must be positive"})
        }

    try:
        orders.put_item(
            Item={
                "orderId": order_id,
                "amount": amount,
                "status": "RECEIVED"
            },
            ConditionExpression="attribute_not_exists(orderId)"
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {
                "statusCode": 200,
                "body": json.dumps({"orderId": order_id, "status": "ALREADY_RECEIVED"})
            }
        raise

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"orderId": order_id})
    )

    return {
        "statusCode": 202,
        "body": json.dumps({"orderId": order_id, "status": "RECEIVED"})
    }


def process_order(event, context):
    failures = []

    for record in event.get("Records", []):
        try:
            message = json.loads(record["body"])
            order_id = message["orderId"]

            orders.update_item(
                Key={"orderId": order_id},
                UpdateExpression="SET #status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "PROCESSING"}
            )
        except Exception:
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}
~~~

Đây là handler học tập. Trong production, cần thêm schema validation, authentication, idempotency key bền vững, trạng thái workflow, error classification, structured logs và logic payment/inventory thực tế.

Ví dụ ghi DynamoDB rồi gửi SQS là hai thao tác riêng. Nếu ghi database thành công nhưng gửi message thất bại, order có thể ở trạng thái RECEIVED mà chưa được xử lý. Production nên cân nhắc transactional outbox hoặc DynamoDB Streams để phát event từ thay đổi dữ liệu, kèm idempotent consumer và cơ chế reconciliation.

### Bước 4: build và deploy

~~~bash
sam build
sam deploy --guided
~~~

Chọn stack name, Region và xác nhận các quyền triển khai. Sau khi deploy, lấy OrdersApiId trong CloudFormation outputs và ghép thành API URL của Region đó.

### Bước 5: gửi request

~~~bash
curl -X POST "$ORDERS_API_URL/orders" \
  -H "Content-Type: application/json" \
  -d '{"orderId":"order-lab-001","amount":125000}'
~~~

Kết quả mong đợi là HTTP 202 và JSON có orderId cùng trạng thái RECEIVED. Worker Lambda đọc message từ SQS và cập nhật trạng thái trong DynamoDB.

### Bước 6: kiểm tra lỗi và DLQ

- Xem Lambda logs trong CloudWatch.
- Xem số message trong SQS queue.
- Tạo một test message sai schema để quan sát retry.
- Kiểm tra message sau nhiều lần nhận được chuyển vào DLQ.
- Thử redrive message sau khi sửa lỗi.
- Kiểm tra DynamoDB record có trạng thái phù hợp.

### Bước 7: cleanup

~~~bash
sam delete
~~~

Xác nhận stack lab đã bị xóa và không còn log groups, queues hoặc tài nguyên ngoài stack cần giữ lại. Kiểm tra billing dashboard để xác nhận không còn tài nguyên phát sinh phí.

## 24. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lambda timeout | Downstream chậm, timeout quá thấp hoặc deadlock | Xem duration, trace và timeout của từng dependency |
| Lambda throttled | Concurrency vượt quota hoặc reserved concurrency | Kiểm tra ConcurrentExecutions/Throttles và giới hạn downstream |
| Cold start tăng | Package lớn, init code nặng hoặc runtime mới | Đo init duration, giảm package và cân nhắc provisioned concurrency |
| API Gateway trả 5xx | Lambda error, integration timeout hoặc permission | Kiểm tra integration, execution role và Lambda logs |
| SQS message xử lý lặp | At-least-once delivery hoặc visibility timeout không đủ | Idempotency, visibility timeout và partial batch response |
| Queue age tăng | Consumer chậm hoặc concurrency thấp | Scale worker, tăng batch phù hợp và xem downstream bottleneck |
| DLQ tăng nhanh | Poison message hoặc lỗi dữ liệu | Phân loại lỗi, xem payload, sửa consumer rồi redrive |
| Lambda VPC không ra Internet | Thiếu NAT/egress route hoặc security group | Kiểm tra route table, NAT, DNS và egress |
| Fargate task không pull được image | Thiếu ECR permissions hoặc network path | Kiểm tra execution role, NAT/VPC endpoints và security group |
| Step Functions execution thất bại | State input/output, IAM hoặc service integration lỗi | Xem execution history và error/cause |
| DynamoDB throttling | Hot partition hoặc capacity pattern | Phân tích key distribution và access pattern |
| Chi phí tăng đột biến | Retry loop, event storm, log volume hoặc data transfer | Tắt trigger lỗi, giới hạn concurrency và kiểm tra usage metrics |

## 25. Best practices

### Kiến trúc

- Chọn compute theo workload, không theo xu hướng.
- Ưu tiên managed services cho queue, event bus, API và orchestration thay vì tự xây lại.
- Tách request path ngắn khỏi tác vụ dài.
- Dùng event contracts có version.
- Không tạo quá nhiều microservices khi domain chưa cần tách.
- Giữ business logic ở các boundary rõ ràng và tránh chaining Lambda tùy tiện.

### Reliability

- Viết function và consumer idempotent.
- Dùng queue buffer khi downstream không thể xử lý burst.
- Cấu hình timeout, retry, DLQ và partial batch response.
- Giới hạn concurrency để bảo vệ database và hệ thống ngoài.
- Test failure path, duplicate event, timeout và redrive.
- Đặt RTO/RPO và diễn tập DR.

### Security

- Mỗi function/task/state machine có IAM role riêng.
- Dùng resource policies và API authorization phù hợp.
- Lưu secrets trong Secrets Manager/Parameter Store.
- Mã hóa dữ liệu at rest và in transit.
- Dùng private networking/VPC endpoints khi cần.
- Không log dữ liệu nhạy cảm.
- Quản lý dependency và container images qua pipeline bảo mật.

### Performance và cost

- Đo latency end-to-end, không chỉ duration của function.
- Tối ưu package size và initialization.
- Dùng Provisioned Concurrency chỉ khi SLO yêu cầu.
- Chọn batch size theo processing time và payload.
- Dùng cache, connection pooling và database proxy khi phù hợp.
- Theo dõi queue age, concurrency, throttles, error rate và cost per transaction.
- Tính cả API, messaging, data transfer, logs, NAT và database.

### Operations

- Quản lý hạ tầng bằng SAM/CDK/CloudFormation/Terraform.
- Dùng nhiều môi trường và deployment strategy có rollback.
- Chuẩn hóa logs, metrics, traces và correlation ID.
- Đặt alarm theo SLO và business outcomes.
- Theo dõi service quotas và request increase trước khi scale.
- Xây runbook cho DLQ, event replay và downstream outage.

## 26. Bài tập tự luyện

1. Serverless là gì và trách nhiệm nào vẫn thuộc về đội phát triển?
2. Vì sao serverless không đồng nghĩa với zero operations?
3. Khi nào nên chọn Lambda thay vì Fargate?
4. Khi nào nên chọn ECS/Fargate thay vì Lambda?
5. Khác nhau giữa ECS Express Mode và ECS service tự cấu hình là gì?
6. AWS App Runner có còn mở cho khách hàng mới vào tháng 11/2026 không? Lựa chọn thay thế là gì?
7. Khi nào nên dùng EKS thay cho ECS?
8. Khi nào workload cần EC2?
9. Phân biệt API Gateway HTTP API và REST API.
10. Khi nào Lambda Function URL đủ dùng?
11. SQS, SNS và EventBridge giải quyết các mô hình messaging nào?
12. Khi nào dùng Kinesis thay vì SQS?
13. Standard và Express Step Functions khác nhau về thời lượng và execution semantics thế nào?
14. Lambda Durable Functions khác Step Functions ở điểm nào?
15. Vì sao event-driven consumer phải idempotent?
16. SQS visibility timeout nên được tính dựa trên các yếu tố nào?
17. Partial batch response giúp giảm loại retry nào?
18. Reserved Concurrency khác Provisioned Concurrency ra sao?
19. Vì sao Lambda gắn vào public subnet vẫn có thể không truy cập Internet?
20. Khi nào nên dùng DynamoDB và khi nào nên dùng Aurora Serverless?
21. Vì sao một API nên trả job ID cho tác vụ dài?
22. Những thành phần nào có thể làm serverless cost tăng ngoài compute?
23. Làm sao theo dõi một business transaction qua API Gateway, Lambda và SQS?
24. Khi nào nên chọn container thay vì chia ứng dụng thành nhiều Lambda functions?
25. Vì sao cần kiểm thử DLQ redrive và event replay?

### Gợi ý đáp án

1. AWS quản lý phần lớn hạ tầng thực thi; đội phát triển vẫn quản lý code, data, IAM, API, retry, observability và chi phí.
2. Vì ứng dụng vẫn cần deployment, security, monitoring, quotas, incident response và DR.
3. Khi workload ngắn, event-driven, scale theo request và không cần process liên tục.
4. Khi cần container/custom runtime, process dài, worker liên tục hoặc tài nguyên CPU/memory ổn định.
5. Express Mode tự cấu hình nhiều hạ tầng hỗ trợ; ECS service thông thường cho phép kiểm soát chi tiết hơn.
6. Không. App Runner đóng nhận khách hàng mới từ 30/04/2026; đánh giá ECS Express Mode.
7. Khi Kubernetes API, CRDs, operators hoặc CNCF ecosystem là yêu cầu nền tảng.
8. Khi cần OS/kernel/hardware control, GPU hoặc workload legacy đặc thù.
9. HTTP API gọn và rẻ hơn; REST API có API keys, usage plans, request validation, WAF integration và private endpoints.
10. Khi chỉ cần HTTPS endpoint cho một function và không cần API management.
11. SQS là queue, SNS là pub/sub fan-out, EventBridge là event bus/routing theo nội dung.
12. Khi cần ingest stream liên tục, throughput cao và xử lý theo shard/partition.
13. Standard tối đa một năm, exactly-once mặc định; Express tối đa năm phút, async at-least-once và sync at-most-once.
14. Durable Functions checkpoint/replay trong mô hình Lambda code-first; Step Functions là state machine điều phối service integrations.
15. Vì event có thể được giao lại và consumer có thể chạy nhiều lần.
16. Function timeout, batch window và thời gian retry/throttling.
17. Chỉ trả lại message lỗi thay vì xử lý lại toàn batch.
18. Reserved giới hạn concurrency và giữ capacity quota; Provisioned giữ execution environments khởi tạo sẵn và tính phí.
19. Lambda cần VPC egress route/NAT; public subnet không tự cấp public IP hay Internet access.
20. DynamoDB cho key-value/document với access pattern rõ; Aurora Serverless cho SQL, joins và relational transactions.
21. Để không giữ request mở trong lúc tác vụ dài xử lý và cho client truy vấn trạng thái.
22. API Gateway, messaging, Step Functions, database, logs, traces, NAT và data transfer.
23. Dùng correlation ID, structured logs và distributed tracing.
24. Khi cần process liên tục, runtime đặc thù, dependency lớn hoặc workload dài.
25. Để bảo đảm event được replay an toàn, không gây side effect trùng và có thể phục hồi sau lỗi.

## 27. Câu hỏi phỏng vấn

### Serverless có phù hợp với mọi workload không?

Không. Workload cần kernel access, GPU đặc thù, process liên tục hoặc utilization ổn định có thể phù hợp hơn với container trên EC2 hoặc EC2 trực tiếp. Quyết định cần dựa trên thời gian chạy, runtime, state, networking và operational capability.

### Có nên chuyển mọi microservice sang Lambda không?

Không nhất thiết. Một service chạy liên tục, có nhiều endpoint và cần giữ connection có thể hợp với ECS/Fargate. Lambda phù hợp với request/event ngắn. Có thể dùng mô hình kết hợp.

### Vì sao serverless thường cần queue?

Queue tách producer khỏi consumer, hấp thụ burst, hỗ trợ retry và tránh để downstream chậm làm request path kéo dài.

### EventBridge khác SNS như thế nào?

SNS tập trung vào pub/sub fan-out. EventBridge tập trung vào event bus và content-based routing giữa AWS services, SaaS và custom sources. Chúng có thể kết hợp trong cùng kiến trúc.

### Khi nào chọn Step Functions Standard?

Khi workflow dài, cần audit history, callback/human approval hoặc điều phối nhiều bước với semantics rõ ràng.

### Vì sao exactly-once không nên được giả định ở mọi boundary?

Một workflow có thể retry task, event source có thể at-least-once và downstream có thể timeout sau khi đã thực hiện side effect. Idempotency vẫn cần thiết để bảo vệ nghiệp vụ.

### Lambda VPC configuration ảnh hưởng gì đến networking?

Khi gắn VPC, outbound traffic của function đi qua VPC configuration. Cần NAT hoặc VPC endpoints cho các đích tương ứng; public subnet không tự tạo Internet access.

### Làm sao bảo vệ database khỏi Lambda burst?

Dùng Reserved Concurrency để giới hạn function, RDS Proxy/connection pooling, queue buffer và backpressure. Theo dõi database connection count và throttling.

### ECS Express Mode phù hợp với ai?

Đội cần triển khai containerized web applications/APIs nhanh với Fargate, URL, load balancer TLS, autoscaling và monitoring được cấu hình theo defaults, nhưng vẫn muốn tài nguyên hiển thị trong tài khoản AWS.

### App Runner có nên là lựa chọn mặc định cho dự án mới?

Không với khách hàng mới sau ngày 30/04/2026. AWS Decision Guide hiện hành khuyến nghị ECS Express Mode cho trải nghiệm container không cần quản lý infrastructure tương tự.

## 28. Checklist trước khi đưa vào production

### Workload fit

- [ ] Workload pattern và thời lượng thực thi đã được đo.
- [ ] Compute được chọn theo runtime, state, concurrency và networking.
- [ ] Đã đánh giá Lambda, Fargate, ECS Express Mode, EKS và EC2 theo yêu cầu.
- [ ] Các giới hạn và service availability theo Region đã được kiểm tra.

### Architecture

- [ ] API request path không chứa tác vụ dài không cần thiết.
- [ ] Queue/event bus được dùng ở boundary cần decoupling.
- [ ] Workflow nhiều bước có retry/catch và trạng thái rõ.
- [ ] Data store phù hợp access patterns và consistency.
- [ ] Event schema có version và backward compatibility.

### Security

- [ ] IAM role riêng theo workload với least privilege.
- [ ] API authentication/authorization được cấu hình.
- [ ] Secrets không nằm trong source code hoặc logs.
- [ ] Data encryption và key permissions được kiểm tra.
- [ ] VPC routes, security groups và endpoints đúng.
- [ ] Logging không chứa PII hoặc credential.

### Reliability và performance

- [ ] Function/task timeout được cấu hình.
- [ ] Idempotency được triển khai cho side effects.
- [ ] Retry, DLQ, redrive và partial batch response được kiểm thử.
- [ ] Concurrency bảo vệ downstream services.
- [ ] Cold start và provisioned capacity được đánh giá theo SLO.
- [ ] RTO/RPO và DR strategy được xác định.

### Observability và cost

- [ ] Structured logs, metrics, traces và correlation ID có sẵn.
- [ ] Alarm dựa trên SLO và business outcomes.
- [ ] Queue age/depth, throttles và error rate được giám sát.
- [ ] Dashboard và runbooks đã được review.
- [ ] Chi phí compute, API, messaging, database, logs, NAT và data transfer đã được ước lượng.
- [ ] Service quotas và budgets đã được thiết lập.

### Deployment

- [ ] Infrastructure as Code được version control.
- [ ] Pipeline có test, security scan và IaC validation.
- [ ] Có canary/linear/rolling deployment phù hợp.
- [ ] Có rollback và event replay plan.
- [ ] Có môi trường test/staging trước production.

## 29. Tài liệu tham khảo chính thức

- [Choosing an AWS serverless service - AWS Decision Guides](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/choosing-aws-serverless-service.html)
- [Choosing a modern application strategy - AWS Decision Guides](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/modern-apps-strategy-on-aws-how-to-choose.html)
- [AWS Serverless Application Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)
- [The pillars of the Well-Architected Framework - Serverless Applications Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/the-pillars-of-the-well-architected-framework.html)
- [Designing Lambda applications](https://docs.aws.amazon.com/lambda/latest/dg/concepts-application-design.html)
- [Lambda invocation methods](https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html)
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [Lambda Durable Functions](https://docs.aws.amazon.com/lambda/latest/dg/durable-functions.html)
- [Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Lambda VPC configuration](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [Enable internet access for VPC-connected Lambda functions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html)
- [Amazon ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)
- [AWS App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)
- [AWS Fargate documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Fargate task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html)
- [Choose between REST APIs and HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Creating and configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Choosing workflow type in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html)
- [Step Functions service integrations and IAM policies](https://docs.aws.amazon.com/step-functions/latest/dg/service-integration-iam-templates.html)
- [Amazon DynamoDB documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Amazon Aurora Serverless](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless.html)
- [AWS Serverless Application Model](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [AWS CDK Developer Guide](https://docs.aws.amazon.com/cdk/v2/guide/home.html)


